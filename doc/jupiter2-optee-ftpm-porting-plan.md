# Milk-V Jupiter2へのOP-TEE・fTPM TA移植計画

対象はSpacemiT K3（RV64）搭載のMilk-V Jupiter2 SBC。調査基準はJupiter2の
`main`（`cf42df851`）。実装・試験の計画と進捗を記載する。

## 目標と進め方

移植のベースは、**Jupiter2リポジトリの現行Keystone構成一式**とする。
改造OpenSBI＋Keystone SM、FSBL/U-Bootからの既存RAM起動・統合FIT生成手順、
`linux-k3/` とDTB、K3 QEMU、rootfs、Keystoneの検証環境にOP-TEEとfTPM TAを追加する。
同居構成の既定起動ではKeystoneとOP-TEEの両方を利用できるようにする。
最初の実機到達点は、同一ファームウェア・Linuxの起動中にKeystone Enclaveと
fTPM TAが動作し、LinuxからTPM 2.0コマンドを実行でき、試験用NVデータが
再起動・電源再投入後にも残ること。Measured Boot・IMAと製品向けの鍵管理は後続とする。

呼び出し経路は、`tpm2-tools → /dev/tpmrmN → tpm_ftpm_tee → Linux OP-TEE
（SBI MPXY）→ OpenSBIのOP-TEEドメイン → fTPM TA`。
TAの読み込みやストレージのRPCには、選択した構成に応じて `tee-supplicant` が関与する。

| 項目 | 現状と採用方針 |
| --- | --- |
| 起動 | [現行のKeystone RAM起動手順](jupiter2-ram-boot-procedure.md)と[統合FIT生成スクリプト](../scripts/build-jupiter2-ram-boot-image.py)を拡張する。 |
| OpenSBI | [改造OpenSBIのK3 Keystone構成](../opensbi/platform/generic/configs/k3_keystone_audit_defconfig)と[既存MPXY dispatcher](../opensbi/lib/utils/mpxy/fdt_mpxy_opteed.c)を使う。`CONFIG_K3_KEYSTONE_SM` で[無効化されているドメイン切替](../opensbi/lib/sbi/sbi_domain_context.c)は、SMと共通の隔離・遷移設計を実装してから有効にする。 |
| Linux | `linux-k3/` と現行K3/Bianbu defconfigを起点に[MPXY経路](../linux-k3/drivers/tee/optee/mpxy_sbi.c)と[fTPMドライバー](../linux-k3/drivers/char/tpm/tpm_ftpm_tee.c)を使う。同じImageでKeystone driverとTEE・TPMを利用する。 |
| OP-TEE・TA | SpacemiTの `k3-br-v1.0.y` を、現行MPXY ABIに合うOP-TEE本体とブート・DT差分の参照元とする。`optee_ftpm` とMicrosoft TPM 2.0参照実装を固定し、K3のTA ABIでビルドする。 |

## 第1・第2段階の進捗

- OpenSBIのMPXY共有メモリーサイズ修正（KSB-045、`d32afa86c`）を取り込み、
  K3 Keystone構成の `fw_dynamic.bin` をビルドした。K3 QEMUで16 hartの
  ファームウェア起動を試し、OpenSBI v1.6のバナーとSMタイマー初期化ログを確認した。
  この試行にはLinuxとOP-TEE payloadを含めていない。
- K3用OP-TEE本体を `2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59` からRV64向けに
  ビルドした。[同居検証プログラムと検証用TA](../verifications/optee-coexistence/README.md)
  を追加し、RV64向けのホスト実行ファイルと署名済みTAを生成した。
  ホストのリンクにはoptee_client `9f4414f62dfc5692fd39f760515ce2d344d07b6d` を使用。
- `scripts/run-k3.sh` に `--dtb FILE --optee-elf FILE` を追加した。
  QEMUのgeneric loaderはELFの物理アドレスにロードし、CPUの開始PCはファームウェアに委ねる。
  16 hart・2 GiBのK3 QEMUで、予約領域を追加したDTBと `tee.elf` を渡し、
  QMPで物理アドレス `0x171000000` のELFロード部分を読み出して元ファイルと照合した。
  この試行ではCPUを停止したままロード内容を検査した。
- OPTEED dispatcherに呼出元domainとABI長の検査を追加し、切替結果をMPXYに
  返すようにした（KSB-074、`4b0f75220`）。現行のKeystone構成では切替が
  未対応のため、dispatcherで共有メモリーやcontextを更新する前に要求を拒否する。
  通常K3構成とK3 Keystone構成をビルドし、後者のファームウェア起動ログを
  16 hartのK3 QEMUで確認した。
- [QEMU用DTB生成スクリプト](../scripts/prepare-k3-qemu-optee-dtb.py)で、
  K3既定のCore領域（`0x171000000`）と静的共有領域（`0x172000000`）を
  それぞれ16 MiB、`reserved-memory` に `no-map` 付きで追加できる。
  QEMUの `dumpdtb` で得たDTBに下記のドメイン定義を加えたファイルを入力に
  `python3 scripts/prepare-k3-qemu-optee-dtb.py base.dtb boot.dtb` を実行し、
  出力を起動スクリプトの `--dtb` に指定する。開発ホストでは `fdtput` が必要。
  16 hart・2 GiBで生成したDTBとOP-TEE ELFを渡してOpenSBIの起動ログを確認した。
  既存予約との重複と、1 GiBで対象範囲がRAM外になる場合は生成を拒否した。
  この予約はLinux向けのメモリー配置情報であり、PMPによる隔離は別途実装する。
- DTB生成ではOPTEED参照とLinux側のmailbox・OP-TEEノードを毎回追加する。
  入力には `/chosen/opensbi-domains` 配下の `optee-domain`（`phandle` 必須）と
  `untrusted-domain` が必要。既存DTBに別のtrusted domain名を使う場合は
  `--mpxy-domain NAME` で指定する。既存K3のチャネル `0x1000`〜`0x100f` を
  hart順で生成し、Linux側ではTEEプロトコルID 2と組み合わせる。
  生成結果はQEMU由来のDTBに試験用domainノードを加え、`fdtget` で照合した。
  この検査にドメインの起動やPMP切替は含まれない。
- 同居のOP-TEE先行起動試験では `--optee-first` を指定する。入力の
  `untrusted-domain` にhart 0のCPU phandleを指す `boot-hart` と、Linuxの
  `next-addr`（このQEMUプロファイルでは `0x102200000`）を設定する。
  全16 hartを起動時にOP-TEEへ割り当て、DTBの物理範囲 `0x181e00000` から
  2 MiBとGEU・PMUMAIN・PMU APの定義を固定PMP計画に含める。
- DTB生成時に、OP-TEEのS-mode開始アドレス（`0x171000000`）と
  Core・共有領域のOpenSBIドメイン権限を検査する。CoreはOP-TEE側でRWX、
  Linux側でアクセス不可とし、共有領域は両側でRWとする。
  各領域へのより小さいポリシーの重複も拒否する。
  試験用DTBで意図した設定を受理し、Linux側にCoreの読み出し権限を付けると
  DTB生成を拒否することを確認した。
- OpenSBIがドメイン設定を認識するため、`/chosen/opensbi-domains` の
  `compatible = "opensbi,domain,config"` をDTB生成時に必須とした。
  **ホスト側検査**ではこの属性が欠けた入力を拒否することを確認した。
  **QEMUファームウェア試験**では、16 hart・2 GiBのK3 QEMUに試験用DTBと
  OP-TEE ELFを渡し、OpenSBIのUARTログで両ドメインの登録、Core・共有領域の
  権限、OP-TEEのS-mode開始アドレスを確認した。hartはrootに置いたままで、
  Linuxを起動せず、OP-TEEへの制御移行も行っていない。
- DTB生成は16 hartを初期状態で `untrusted-domain` に割り当て、
  両ドメインの `possible-harts` に登録する。両ドメインに `phandle` が必要。
  **QEMUファームウェア試験**では、この割当てで起動し、boot hartの
  `untrusted-domain` 所属と、Core領域のS/Uアクセス禁止・共有領域RWに対応する
  PMP設定のOpenSBI読戻し成功をUARTで確認した。LinuxとOP-TEEは未起動。
- **QEMUのS-mode引き渡し試験**では、Linuxの代わりに
  [最小ペイロード](../verifications/optee-coexistence/README.md)を起動した。
  16 hart・2 GiBで、boot hartの `untrusted-domain` 所属、Keystone SMの
  初期化完了、`0x102200000` のペイロードからのSBIコンソール出力を確認した。
  OP-TEE ELFもロードしたが、OP-TEEへの制御移行は行っていない。
- **QEMUのLinux起動試験**では、Debianの
  `6.12.107+deb13-riscv64` と[最小initramfs](../verifications/optee-coexistence/README.md)を
  使い、同居用DTB、Keystone SM入りOpenSBI、OP-TEE ELFを渡した。
  UARTでLinuxの `/init` 実行と16 CPUオンラインを確認した。
  比較用のDebianカーネルでの結果で、Jupiter2の `linux-k3` では未確認。
  OP-TEEはELFのロードまでで、Enclave実行とTA呼び出しも未実施。
- **Jupiter2のLinux・Keystoneゲスト試験**では、`a70e2fae0` の
  `linux-k3` 6.18.3から16 hartのQEMU試験用Imageをビルドし、
  同じカーネルのシンボル情報でビルドした `keystone-driver.ko` をロードした。
  カーネルはSMP、FPU/Vector、APLIC/IMSIC、CMA、モジュール、initramfsを
  有効にした最小構成を使用。カーネルImageのSHA-256は
  `b6fc49c85c714892cdd038ba6d534f4f103cc177bd17fb94f9508767d3ffab3b`。
  同居用DTB、16 hart・2 GiBのK3 QEMUで、16 CPUオンラインと
  `hello`・`hello-native` のEnclave実行、終了値0、DESTROY成功を確認した。
  初回のDTBでは `untrusted-domain` にリセット権限がなく、電源断が完了しなかった。
  試験用DTBに `system-reset-allowed` を追加した再試験でも両サンプルが成功し、
  QEMUは電源断後に終了コード0を返した。OP-TEEはELFのロードまで。
- **QEMUでのOP-TEE単独TA試験**。通常K3 OpenSBI、`linux-k3` 6.18.3
  （TEE・OPTEE・MPXY mailbox内蔵）、OP-TEE Core
  `2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59` を使用。
  K3実機向け既定設定では鍵管理初期化中にeFuse MMIOへのアクセスでdata-abortした。
  QEMU試験用として `CFG_K3_EFUSE=n CFG_K3_PRNG=n CFG_K3_IOPMP=n
  CFG_TE200_CRYPTO_DRIVER=n CFG_MMP_RTC=n CFG_DRIVERS_RTC=n CFG_RTC_PTA=n`
  でビルドし、実効設定は `CFG_WITH_SOFTWARE_PRNG=y`、
  `CFG_K3_HUK_ALLOW_UNFUSED=y`。開発用HUKを許す構成である。
  QEMUは16 hartで起動し、試験用DTBでhart 0のみを有効にした。
  OP-TEEは1 core・1 thread、MPXYはチャネル `0x1000`、
  検証用TAは `EARLY_TA_PATHS` で組み込んだ。
  Linuxユーザー空間で `TEEC_InitializeContext` と `TEEC_OpenSession` が成功し、
  TAへの入力41に対して42と所定のマーカーが返ったことをUARTで確認した。
  この試験の合格範囲はOP-TEE単独のMPXY・TA往復。Keystone同居、
  16 hartでのOP-TEE動作、fTPM、ハードウェア保護は未検証。
- **QEMU eFuse読出し試験**。K3 QEMUの `wtm-rng=on` に、既存のPMU
  クロックモデルと連動する未書込みGEU eFuse（物理アドレス
  `0xf0702800`、サイズ `0x400`）を追加した。GEUのreload要求と開始を
  受け取り、readyを返す。ヒューズバンクはゼロを返し、書込みによる
  プログラミングは扱わない。OP-TEE Coreは
  [PMUマッピング修正](../patches/optee/k3-map-efuse-clock-registers.patch)を
  上記固定コミットへ適用し、`CFG_K3_EFUSE=y` で再ビルドした。
  試験用DTBでGEU、PMUMAIN（`0xd4050000`、PMP範囲16 KiB）、
  PMUAP（`0xd4282000`、4 KiB）へのアクセスをOP-TEE側だけに許可した。
  同じDTB・OP-TEE ELFでモデルを無効にするとPMUMAIN読出しでdata-abortし、
  有効にすると未書込みバンクを検出して開発用HUKへ進み、Linuxからの
  検証用TA往復が成功した。1 hart有効の単独試験で、他のハードウェア依存設定は
  前項と同じ。実機固有のHUK、ヒューズの書込み、IOPMP、TE200、RTCの動作は未検証。
- **QEMUの16 hart OP-TEE単独試験**。同じ通常K3 OpenSBI、`linux-k3`、
  `CFG_TEE_CORE_NB_CORE=16 CFG_NUM_THREADS=16 CFG_K3_EFUSE=y` のOP-TEE Core、
  16チャネルのDTBを使用。標準のOpenSBIヒープではCPU 13の初期化ログで止まり、
  `opensbi,config` の `heap-size` だけを256 KiBにすると16 CPUがオンラインになった。
  [ゲストテスト](../verifications/optee-coexistence/optee-16-hart-init.c)を各CPUに順に
  固定し、TAが入力41を42に変換してマーカーを返すことを16件すべてで確認した。
  同居用DTB生成にも256 KiBの最小値を設定し、その生成結果でKeystoneの
  `hello` と `hello-native` が引き続き成功することを別のQEMU起動で確認した。
  同一ゲストでのKeystone・OP-TEE同居およびTA並行呼出しは未実施。
- **QEMUの16 hart並行呼出し**。通常K3 OpenSBIと同じOP-TEE Coreを使い、
  `-accel tcg,thread=multi` で実行。ゲストで16子プロセスを一斉に解放し、
  CPUごとに異なる入力とTAの応答を照合した。全子が成功し、
  `PASS: parallel OP-TEE TA calls on all 16 CPUs` を確認した。
  試験終了後のQEMU電源断はタイムアウトした。
- **QEMUの同一ゲスト同居試験**。Keystone SM入りOpenSBI、同居用DTB、
  TEEとMPXYを含む `linux-k3` 6.18.3、対応するKeystoneドライバーを使用。
  Linuxは16 CPUで起動し、MPXY mailboxの16チャネルを登録した。
  OP-TEEのprobeはMPXYエラー `-524` の後に `-22` で失敗し、
  同居テストは `TEEC_InitializeContext=0xffff0008` で停止した。
  同じゲストで実行したKeystone `hello-native` は終了値0・DESTROY成功。
  OP-TEEへのドメイン切替を安全に行うPMP実装が未完了のため、同居は不合格。
- **各hartでの直接切替に向けたKeystoneの割当て検査**。
  K3のEnclave作成時にEPMとUTMの両範囲について、呼出元OpenSBIドメインの
  S-mode読み書き権限を検査する。Linux側ドメインでアクセス不可のOP-TEE Core
  領域は、この検査によりEID割当て・PMP更新前に除外される。
  16 hartのK3 QEMUで同居用DTBと `linux-k3` を起動し、Keystoneの
  `hello`、`hello-native`、電源断が成功した。保護領域を指定する拒否試験、
  両ドメインが読み書きできるTEE共有領域の専用予約、PMP切替と同居は未確認。
- **固定PMPスロットの起動時割当て**。2 GiBのK3 QEMU用DTBにGEU、
  PMUAP、PMUMAINと起動DTBのポリシーを追加した。起動DTBはRAM末尾の
  2 MiB（`0x181e00000`〜`0x181ffffff`）を `no-map` で予約する。
  16 hartの実QEMUで、OpenSBIが `opensbi-mask=0x83ff` と
  `keystone-mask=0x7c00` を設定し、全hartでPMPの読戻しが成功した。
  この構成での実スロット順は、0〜2がGEU・PMUAP・PMUMAIN、3〜5が
  M-mode用APLIC・タイマー・IMSIC、6がファームウェア、7が起動DTB、
  8・9がCoreと共有RAM、10〜14がKeystoneの動的枠、15がフォールバック。
  Linuxの `hello` と `hello-native` は成功し、電源断も完了した。
  実行時の権限切替、OP-TEE同居、動的枠の枯渇試験は未実施。
- **実行時切替の対象範囲の検査**。Keystone構成のOPTEED初期化で、
  trusted domainがアクセスする各範囲が、OpenSBIの固定スロットと
  アドレス・サイズ・MMIO種別まで一致するか検査する。ファームウェア保護枠、
  Keystone動的枠、全範囲フォールバックは対象から外す。
  実QEMUで固定対象マスク `0x387`、Keystoneマスク `0x7c00` を確認し、
  `linux-k3` の16 CPUでKeystoneの両サンプルと電源断が成功した。
  trusted domainに全範囲RWXを追加したDTBでは検査が拒否し、
  Linux側ドメインへの最小S-modeペイロード引き渡しは成功した。
  この段階ではPMP CSRの実行時更新とOP-TEEへの制御移行は行わない。
- **固定PMPスロットのCSR書込み・復元試験**。各hartの起動時にM-mode内で
  フォールバックを拒否に変更し、OP-TEE用の固定枠に権限を設定して読み戻す。
  続いて固定枠をLinux側の権限に戻し、フォールバックを最後に復元する。
  読戻しに失敗したhartはS-modeへ進めない。
  16 hartのK3 QEMUで往復の成功ログを全hartで確認し、復元後に同じ
  `linux-k3` ゲストでKeystoneの両サンプルと電源断が成功した。
  OP-TEEの権限が有効だった間にS-modeへは移行していない。
- **固定PMP切替の開始状態検査と復旧処理**。Linux側からOP-TEE側、
  OP-TEE側からLinux側の両方向で、それぞれ書込み前に元のアドレス・形状・権限を
  PMP CSRから読み戻す。適用エラー時は元の権限を設定し直して検査し、
  復旧を確認できない場合はhartを停止する。成功・復元後は `sfence.vma` を行う。
  16 hartのK3 QEMUで、この処理による起動時の往復と、
  復元後のKeystone `hello`、`hello-native`、電源断を確認した。
  CSR書込みの故障注入や、実行中のドメイン切替は未試験。
- **OP-TEE専用範囲とKeystone割当ての分離**。検証済みのOP-TEEドメインが
  S/U-modeでアクセスできる範囲は、Keystone CREATEのEPM・UTM・backingから
  除外する。Linuxも読み書きできるTEE共有RAMと起動DTB領域も対象とする。
  16 hart K3 QEMUのLinuxゲストで試験用カーネルモジュールを実行し、
  共有RAMと起動DTBを別々にUTMとして指定するとCREATEが
  `SBI_ERR_SM_ENCLAVE_REGION_OVERLAPS`（100006）を返すことを確認した。
  同じゲストでKeystoneの `hello`、`hello-native` と電源断も成功した。
  OP-TEEへの実行中の切替はこの試験に含めていない。
- **ドメイン切替用のPMPインターフェース**。登録済みのLinux・OP-TEE間の
  遷移に限定し、遷移先の対象hart、Enclave実行状態、Keystone枠に有効な
  S/Uアクセス許可がないことを検査する。Linux側の配置から固定枠を再構成するため、
  OP-TEE側からの復元でも同じPMP番号を使える。
  この処理と共通のCSR更新経路を起動時に16 hartすべてで往復試験し、
  復元後のKeystone両サンプルと電源断をK3 QEMUで確認した。
- **固定PMP更新をドメイン切替に接続**。K3 Keystone構成では、固定枠の権限更新が
  成功した後にhartの所属、呼出元情報、CPUコンテキストを切り替える。
  更新に失敗した場合は、所属と呼出元情報を保持してエラーを返す。
  K3 QEMUのKeystone単独構成で `hello` と `hello-native`、OP-TEE単独構成で
  16 CPUからの並行TA呼出しを確認した。K3 Keystone構成のMPXYからの切替は
  抑止したままなので、接続した経路のQEMU実行は未確認。
- **タイマー処理**。`5008b3157` で試験的に追加した `stimecmp` の保存・復元を
  取り消し、取り込み済みOpenSBIのタイマー処理に戻した。同居試験でKeystoneの
  追加に起因するタイマーの問題が再現した場合は、その原因に絞って修正する。
  取り消し後のK3 QEMUで、OP-TEE単独構成は全16 CPUの並行TA呼出しに成功した。
  同居構成ではLinuxが16 hartで起動し、Keystoneの `hello-native` は動作したが、
  OP-TEEのMPXY要求は既存のガードで拒否され、`TEEC_InitializeContext` は
  `0xffff0008` を返した。
- 残作業は、実起動用DTBの残りのメモリー・MMIOポリシーの確定、共通PMP
  ポリシーとhart間同期を伴うドメイン切替、ゲストでの通信と逐次・並行試験。
  現行のK3 Keystone構成ではドメイン切替を抑止している。

## 実装順序と完了条件

### 1. 改造OpenSBIでOP-TEE通信を有効にし、K3 QEMUで確認する

- 現行の改造OpenSBI＋Keystone SM、`linux-k3`、K3 QEMUのコミットと設定を固定し、
  基準構成を起動してKeystone既存検証の結果を記録する。SpacemiT SDKから、
  現行MPXY ABIに対応するOP-TEE本体と必要なブート・DT差分を特定する。
- [同居設計](keystone-optee-coexistence-design.md)に沿って、既存MPXY dispatcherを
  Linux・Enclave・OP-TEEの共通PMPポリシーとドメイン切替に接続する。
  hart間同期、CPU状態の保存・復帰、呼出元の認可、RPC・割込み・タイマー、
  切替失敗時の復旧を扱う。保護を維持できる切替経路の実装後にドメイン切替を有効にする。
- K3 QEMUのpayloadロード・DT生成、LinuxのMPXY/mailboxとTEE設定、
  rootfsのlibteecと `tee-supplicant` を揃える。固定したOP-TEEをQEMU用にビルドし、
  同一ゲストでOP-TEE初期化、LinuxのTEE登録、既存Hello World TAの呼出し、
  Keystone Enclaveの動作を確認する。
- **成果物・完了条件**。改造OpenSBIの変更、再現用のビルド・起動手順とUARTログを残す。
  QEMU上で実Linux → SBI MPXY → 改造OpenSBI → OP-TEEの往復が成功し、
  Keystoneの基準試験を再実行できること。

### 2. 通信・同居のテストプログラムを作り、K3 QEMUで確認する

- `verifications/` にLinux側テストプログラムと検証用TAを追加する。
  同じプロセスでTAセッションとKeystone Enclaveを開き、TAへの入力と応答を照合し、
  Enclave呼出しと交互に反復する。必要なRPC・OCALL後の復帰も確認する。
- 現行K3 QEMUは16 hart構成を要求する。まず単一hartに試験プロセスを固定して逐次試験を行い、複数hartの並行試験へ進む。共有領域の正常アクセス、
  保護領域の隔離、通信・遷移の失敗時の復帰、既存Keystoneの回帰を確認する。
  試験は実K3 QEMUゲスト、Linuxドライバー、OpenSBI/SM、EnclaveとTAを通して実行する。
- **成果物・完了条件**。テストソース、ビルド・ゲスト内実行手順、期待値、
  実行結果を揃える。失敗・スキップと、QEMUで検証できる範囲を記録する。

### 3. 改造OpenSBIの実機テスト手順書を作成する

- [既存のKeystone RAM起動手順](jupiter2-ram-boot-procedure.md)を基に、
  対象機材・起動媒体の確認、現行環境のバックアップ、成果物のハッシュ照合、
  統合FITの生成・RAM転送、UARTでの起動確認、元の構成への復帰を記載する。
  既存のFSBL/SPLとU-BootがOP-TEE試験用payloadを渡せるかを確認し、
  必要な場合は対応するローダー、ロード先、OpenSBI用DTとLinux用DTBを指定する。
- 第2段階のテストプログラム・検証用TAを使い、改造OpenSBIの通信、ドメイン切替、
  Keystone回帰を実機で確認できるようにする。コマンドの実行場所、期待ログ、
  合否・中止条件、採取するUARTログと `dmesg` を明記する。
- **担当と成果物**。Codexが実機テスト手順書と試験に必要な成果物一覧を作成する。
  実機での操作・試験はユーザーが実施する。実機の合否は提供されたログに基づいて記録する。

### 4. OP-TEEとfTPM TAをクロスコンパイルし、実機への配置手順を示す

- 固定したK3 OP-TEEから、実行環境と同じABIのTA dev kitを出力する。
  `TA_DEV_KIT_DIR` と `CFG_MS_TPM_20_REF` を指定してTAをビルドし、
  生成ELFのアーキテクチャ、署名前後の成果物、OP-TEE側のTA署名検証を確認する。
  初期候補の `optee_ftpm` には `-D_ARM_` があるため、適用箇所を調べ、
  RV64での整数幅、アラインメント、時刻、乱数、NVアクセスへの影響を評価する。
  Measured BootとPPIは初回試験では無効とする。
- ビルド試行では K3 OP-TEE `2fbd6ae54d89` のRV64 dev kit、`optee_ftpm`
  `f09f4cdad210` および指定のMicrosoft参照実装 `98b60a44aba7` を使用した。
  参照実装がRV64の `RADIX_BITS` を自動判定できず、試験用に64を明示すると
  コンパイルはTAヘッダーまで進んだ。現行dev kitには候補版が要求する
  `TA_FLAG_INSTANCE_KEEP_CRASHED` がなく、この候補版のビルドは停止した。
  対応候補は、フラグ導入前の互換fTPM版を固定する方法と、対応するOP-TEE Coreの
  動作をK3版へ移植する方法。定義だけを追加してもクラッシュ後のセッション動作は揃わない。
- QEMUの初期試験ではフラグ導入直前の `6f99e783eb9b` を使用し、署名済みRV64 TAを
  生成した。K3 QEMUの16 hart同居構成でREEからTAをロードし、libteec経由の
  `TPM2_GetRandom(16)` が成功した。ビルドと再現手順は
  [fTPM TAのビルドとQEMU試験](jupiter2-ftpm-ta-test.md)を参照。
  `k3_bianbu_defconfig` で `tpm_ftpm_tee` を既定モジュールにし、QEMUで
  `microsoft,ftpm` のDTノードから登録した `/dev/tpmrm0` 経由でも
  `TPM2_GetRandom(16)` の応答を確認した。KSB-084の修正後は16 hart QEMUで
  モジュール登録から電源断まで反復試験に成功した。実機での動作は未確認。
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

- 開発ホストでRV64向けOP-TEE本体とfTPM TAをクロスコンパイルする。
  統合FITに組み込むOP-TEE payload、署名済みTA、対応のLinux Image・DTB・必要な
  モジュール、libteec・`tee-supplicant` の版、配置先とハッシュを一覧化する。
  実機手順には、ホストでのビルド、FITへの組み込み、実機への転送・RAM起動、
  rootfsへのTA配置、サービス・ドライバーの起動順、元の構成への復帰を含める。
  永続媒体へ配置する場合は対応区画と復旧手順を確定する。
- **担当と成果物**。Codexがクロスコンパイル済み成果物と実機deploy手順を揃える。
  実機への配置と下表の確認はユーザーが実施する。第3段階の結果を確認してから、
  fTPMを含む構成の実機試験へ進む。

| 試験 | 合格条件 |
| --- | --- |
| TPMコマンド | `tpm2_getcap properties-fixed`、`tpm2_getrandom 16`、利用可能なバンクで `tpm2_pcrread` が成功する。 |
| PCR動作 | 評価専用のPCRへ既知ダイジェストをextendし、読み出した値が期待値と一致する。起動後のPCRは対象の起動種別に応じて評価する。 |
| NV永続化 | 評価専用NV indexを定義し、既知データを書き、通常再起動と電源再投入の後で一致を確認する。既存のTPMデータに触れず、試験用indexを後片付けする。 |
| RPC・ストレージ障害 | 評価用環境でsupplicant未起動・再起動、ストレージ利用不可を試し、エラーが観測でき、復旧後に既存NVデータが保たれることを確認する。 |
| 同一プロセス・並行動作 | 同一LinuxプロセスでKeystone SDKとTPMデバイスを開き、Enclave呼出しとTPMコマンドを交互に実行する。複数hartで並行に実行し、RPC・OCALL・割込み後に双方が正しく復帰する。 |
| 隔離と回帰 | Linux・Enclave・OP-TEE間の保護領域へのアクセス制御、共有領域の正常アクセス、遷移失敗時の回復を確認する。実機のPMP/DMA隔離を確認し、既存Keystone suiteとOP-TEE対象試験の結果を基準と照合する。 |
| 起動回帰 | 基準構成と同居構成でLinuxの起動・停止を確認し、起動媒体・CPU構成・メモリー容量を記録する。 |

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
- **Measured Boot・IMA**。ブート側のイベントログ、OP-TEEのイベントログ取得
  API、Linux側のTPM選択を揃え、イベントログの再生結果とPCRを照合する。
  [既存のKeystone PCR・Quote設計](keystone-tpm2-quote-design.md)との
  測定先の選択はこの段階で決める。

## 参照

- [SpacemiT SDKのOP-TEE構成調査](optee-milk-v-jupiter2.md)
- [OpenSBIへの取り込み計画](optee-opensbi-keystone-merge-plan.md)
- [Jupiter2の永続ストレージ調査](jupiter2-persistent-storage-investigation.md)
- [Jupiter2のセキュリティエンジンと乱数](jupiter2-security-engine-rng.md)
- [OP-TEE fTPM TAの初期候補（固定コミット）](https://github.com/OP-TEE/optee_ftpm/tree/f09f4cdad21028289d4e8fc573893b75f7228dc7)
- [上記TAが指定するMicrosoft TPM参照実装](https://github.com/microsoft/ms-tpm-20-ref/tree/98b60a44aba79b15fcce1c0d1e46cf5918400f6a)
