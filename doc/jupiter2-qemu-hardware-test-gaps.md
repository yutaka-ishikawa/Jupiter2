# Jupiter2実機試験から判明したQEMUの不足と追加検証

更新：2026年11月21日。今回の実機試験で分かった条件を、QEMUモデルの変更と試験条件の追加に分けて整理する。
QEMUの現在のモデルは `virt` を基にした部分モデルであり、実機の起動チェーン全体を再現していない。
この制約は[実機互換性調査](../hardware/jupiter2/jupiter2-hardware-compatibility.md)でも記録していたが、
Keystoneの検証に必要な実機条件を回帰試験へ取り込む作業が不足していた（KSB-072）。

## 1. 今回の問題をQEMUで検出できなかった理由

従来の `scripts/run-k3.sh` は全Hartへ同じCPU設定を指定していた。

```text
rva23s64,k3-pmacfg=true,pmp=true,num-pmp-regions=16,pmp-granularity=16
```

ここで `pmp-granularity=16` は16 **バイト**であり、実機の4 KiBとは異なる。
OpenSBIログの `log2gran=12` は4096バイトを意味する。

実機はX100が16 PMP、A100が32 PMPだが、QEMUの試験では全Hartが16 PMPだった。
そのため「個数が16以外なら拒否」という移植コードの不備は試験対象にならなかった。
QEMUが32 PMPを扱えないという意味ではない。指定した試験構成に32個のHartがなかった。
また、QEMUの簡略なdomain/予約メモリー構成は実機のroot PMP規則数やロック配置とも一致しない。
QEMUのPASSは、その入力構成に対する結果であり、実機構成への適合証明ではなかった。

## 2. 不足一覧と優先順位

| 優先度 | 実機で判明した条件 | 必要な対応 | 今回の対応状況 |
| --- | --- | --- | --- |
| P0 | X100=16、A100=32 PMP（KSB-071） | Hart別のPMP数を再現し、混在したまま全Hart起動・Enclave同期を実行 | `mixed-pmp` オプションを追加 |
| P0 | PMP粒度4 KiB。256バイトのRPMI doorbell領域が表現できない（KSB-058） | 混在プロファイルを4096バイト粒度にし、小領域の拒否・ページ単位の保護を検証 | 混在プロファイルの粒度を修正。実機domain fixtureは未実装 |
| P0 | rootが13エントリー、Keystone空き3個。RCPU保護にLビットあり（KSB-059/060） | 実機相当のdomain規則・順序・ロックを入力する試験を追加 | 現行QEMUのdomainを実機同等にはしていない。未実装 |
| P0 | OS/UTMのslot共用では実機fallbackと競合（KSB-061/062） | 少数slot、広域fallback、共有regionの解放・再割当てを本物のSMで回帰試験 | KSB-073でUTM復帰も修正し、混在Linux guestでhello二種成功。slot不足・共有解放・実機予約条件の負の試験は未実施 |
| P1 | 実機のPMPADDR実装幅38ビット | WARL上位ビットと範囲境界の実測に合わせたCSRモデル・試験を追加 | 今回の混在実測は54ビット。実機の38ビットへ変更していない |
| P1 | PMP16〜31の初期状態が未採取 | 追加範囲のOFF/ロック/有効規則、特にPMP16のTORロックによるPMPADDR15への影響を検証 | SM/OpenSBIに全数検査を実装。負の条件を作るQEMU診断機構は未実装 |
| P1 | Linux直接mailboxとM-onlyページの所有権競合（KSB-070） | M-onlyページを含む実機相当DT入力、直接アクセスの拒否、SBI経由利用を検証 | 別名Linux DTBの生成・検査を実装済み。QEMUに同じmailbox機器モデルはない |
| P1 | ESOSとAP側RPMI queue/slot/server設定の不一致で起動停止（KSB-069） | 生きたサーバーとの通信、queue不一致や応答timeoutを試験。DT静的検査だけでは不足 | パッケージ作成時の実DT整合検査は実装済み。QEMUの実機ESOS/RCPUモデルは未実装 |
| P1 | 異なるCPUのISA/CSR、PMP同期IPI、Sstc/M-timer、HSM状態遷移 | X100/A100差のうち仕様と実測のあるものを追加し、idle/STOP/START/resumeを検証 | 今回はPMP数と粒度のみ。A100のISA差や全CSRを再現してはいない |
| P2 | FDL/SPL/統合FIT/ESOS entry・handshakeの不整合（KSB-065〜068） | 起動チェーンの入力検査と実機UART試験。全SoC模倣は別開発 | 参照FSBL・FIT作成処理を修正済み。QEMUでFSBL/ESOSを実行していない |
| P2 | UFS初期化失敗と、整合修正後の正常起動（KSB-063） | 実機UFS/RCPU/clock/power連携での確認 | QEMUのvirtio diskはUFSの代替試験にならない。実機試験を継続 |
| P2 | NOR OpenSBI区画384 KiB | 最終ITBの容量検査を配布工程で必須化 | 既存の容量検査・パッケージ作成処理で扱う。通常QEMU起動では検出できない |

mailbox/RPMI/ESOS/UFSの問題をすべて「QEMUのバグ」とはしない。
モデルに存在しない機能の試験が抜けていた、という検証範囲の不足である。
実機のDMA、PMA、キャッシュ、セキュア起動、乱数・attestation品質も、このPMP修正で再現できたとは扱わない。
Linuxログのremoteproc資源処理エラーなど、因果が未確定の表示は別途調べ、PMP起動失敗と一括しない。

## 3. 今回追加したQEMUプロファイル

既存の一律16個の構成を既定として残し、比較用の混在プロファイルを追加した。

| プロファイル | Hart0〜7 | Hart8〜15 | PMP粒度 |
| --- | --- | --- | --- |
| `uniform16`（既定） | 16個 | 16個 | 既存設定の16バイト |
| `mixed` | 16個 | 32個 | 全Hartで4096バイト |

CPUをrealizeする前にHart別の `num-pmp-regions` と `pmp-granularity` を設定し、
QEMU本体のPMP CSR実装を使用する。SBI結果やSM関数をモックには置き換えない。
CPUモデルは両側ともrva23s64のままであり、X100/A100という名前や実装IDを付けて実機再現と見せる変更はしない。

```bash
# 開発PC、publicリポジトリのルート。変更したQEMUもビルドする。
make qemu
make firmware

# 同じカーネル・rootfs・修正版firmwareで比較する。
# install/keystoneへ配置する方法は既存のビルド・配置手順を参照する。
FW=.build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin
bash scripts/run-k3.sh --image keystone --bios "$FW" --pmp-profile uniform16
bash scripts/run-k3.sh --image keystone --bios "$FW" --pmp-profile mixed
```

QEMU直接起動時の指定は `-M jupiter2,mixed-pmp=on`。
未修正のQEMUにはこのpropertyがないため、更新前のバイナリーを使わない。
SMのビルド側 `KEYSTONE_PMP_PROFILE=mixed` は16/32個を許可する既定値。
`KEYSTONE_PMP_PROFILE=qemu16` はSMの証拠検査を16個だけに限定する診断ビルドで、
混在試験・実機試験には使用しない。QEMU起動オプションとSMビルド設定を混同しない。

## 4. 追加すべき回帰試験

1. 同じ修正版firmwareを一律16個と混在構成で起動し、全16 CPUとhello二種を確認する。
2. 混在構成のHart3とHart8からそれぞれCREATE/RUN/DESTROYを行い、全対象HartのPMP反映・readback・ACKを確認する。
3. 実機相当のdomain fixtureを追加し、予約13個、空き3個、ロック付き規則、広域fallbackで実行する。
4. 追加PMP範囲の不正初期状態を実際のCSRへ設定する専用診断経路を用意し、S-modeやCREATEへ進まないことを確認する。
5. 小領域、slot不足、共有slot解放、UTM/EPM配置不成立、同期timeout、idle、hotplugの拒否・復帰経路を実guestで検証する。
6. 実機専用のFDL/ESOS/RPMI/UFSの試験結果を別に記録し、QEMU試験の結果と混ぜない。

新しい試験スクリプトは試験ディレクトリに置き、目的・対象プロファイル・実行場所をコメントに記載する。
上記のうち機構未実装の項目は、手順を記載しただけで実施済みにはしない。
実施状況は[混在PMP修正計画・結果](jupiter2-heterogeneous-pmp-plan.md)へ記録する。


## 5. QEMU設定の検査スクリプト

```bash
python3 scripts/tests/jupiter2-ram-boot/check_qemu_pmp_profile.py \
  --qemu install/keystone/bin/qemu-system-riscv64
```

実QEMUを停止状態で起動し、QMPから全CPUの実設定を読み取る。
両プロファイルのPMP個数と粒度を確認するもので、OpenSBI/SMの実行試験を置き換えない。
スクリプト冒頭にも目的と検証限界を記載している。


## 6. 今回の実測結果

QEMU本体のビルドと両プロファイルのQMP設定検査に成功した。
さらに `run_pmp_hsm_smoke.py` で実OpenSBI/SMを起動し、全16 Hartのroot readbackとSBI HSM経由のS-mode到達が両構成で成功した。
生成物・UARTログは指定したoutput配下へ保存する。

一方、今回のQEMUのroot使用数は7個、空き9個、PMPADDR幅54ビットだった。
実機のroot13個・空き3個・38ビットを再現する試験は追加が必要である。
専用S-mode guestの成功をLinux/SDKのrun-allやEnclave隔離のPASSとはしない。


## 7. 実Linux/SDK/Eyrie/sampleまでの回帰試験を追加

KSB-073では実機と同じ提供sampleを実Linux guestで実行した。
修正前はQEMUでもrunner+0x529cのload access fault・終了139を再現できた。
修正後は両PMP構成×Linux CPU3/8×hello/nativeの計8回すべて正常終了した。
[入力hash・修正箇所・UARTと比較結果](jupiter2-utm-host-access-issue.md#6-実qemuでのsample回帰試験結果)を参照する。
これは全sample suiteや実機domain fixture等の未実装項目が解消したことを意味しない。

## 8. 実機DTBを基準にQEMUの再現範囲を調べる

### 実機の起動DTBを取得する

Jupiter2実機のLinuxで、起動時に渡されたFDTを保存する。

```bash
sudo cat /sys/firmware/fdt > running.dtb
uname -r
sha256sum running.dtb
```

開発PCの `hardware/jupiter2/captures/<採取ID>/running.dtb` にコピーする。
採取IDの付け方と保存する資料は [実機資料ディレクトリ](../hardware/jupiter2/README.md) を参照。
起動方式、Linux・OpenSBIの版、搭載RAM、U-Bootで選んだDTB名も記録する。
`/sys/firmware/fdt` が利用できない場合は、U-Bootが実際に読み込んだ
DTBファイルをコピーする。採取元を「起動後にLinuxから取得」または
「U-Bootの入力ファイル」と明記し、ブートローダーによるfixupの差を区別する。
実機のロード元は [RAM起動ガイド](jupiter2-ram-boot-guide.md) を参照。

QEMUとの照合に進む前に、採取した実機と `hardware/jupiter2/` の
参照資料が同じボード・起動構成を示すことを確認する。
確認項目は [使用する実機との照合](../hardware/jupiter2/README.md#使用する実機との照合) を参照する。

### 同じ検査プロファイルでQEMUのDTBを得る

以下はOP-TEE同居試験の16 hart・2 GiB・WTM RNG有効・均一16 PMP枠の例。
開発PCのリポジトリ直下で実行する。DTBの確認には `device-tree-compiler` が必要。

```bash
CAPTURE_ID=20261124-01  # 実際の採取IDに置き換える
BOARD="$PWD/hardware/jupiter2/captures/$CAPTURE_ID"
WORK="$PWD/.build-k3/dtb-compare/$CAPTURE_ID"
mkdir -p "$WORK"
QEMU="$PWD/install/keystone/bin/qemu-system-riscv64"
"$QEMU" --version
"$QEMU" \
  -M "jupiter2,wtm-rng=on,dumpdtb=$WORK/qemu-base.dtb" \
  -cpu rva23s64,k3-pmacfg=true,pmp=true,num-pmp-regions=16,pmp-granularity=16 \
  -smp 16 -m 2G -bios none -display none

sha256sum "$BOARD/running.dtb" "$WORK/qemu-base.dtb"
dtc -I dtb -O dts -s -o "$WORK/running.dts" "$BOARD/running.dtb"
dtc -I dtb -O dts -s -o "$WORK/qemu-base.dts" "$WORK/qemu-base.dtb"
fdtget -l "$BOARD/running.dtb" /cpus
fdtget -l "$WORK/qemu-base.dtb" /cpus
diff -u "$WORK/running.dts" "$WORK/qemu-base.dts"
```

`diff` の終了値1は差分ありを表す。phandleは参照先のノードで照合する。
実機のLinux起動時DTBとQEMUの素のDTBを比べる場合は、
`/chosen`、initrd、予約メモリなどのうち起動段階で追加された差を別に記録する。
MPXYやOP-TEEの比較には、同居設定を追加した最終 `boot.dtb` も並べて確認する。

| 検査対象 | 照合する内容 |
| --- | --- |
| CPU・PMP | 有効なhart ID、ISA、割り込みコントローラとの接続。PMP個数と粒度はDTBだけで判定せず、QMPの設定と実機OpenSBIのUART結果を照合する。 |
| RAM・予約 | `/memory` の各区間、`/reserved-memory` とFDTの予約リスト、OP-TEE Core・共有領域・起動DTBの範囲。実機とQEMUのRAM容量差も記録する。 |
| 割り込み・周辺機器 | UART、IMSIC/APLIC、タイマー、WTM、eFuse、PMU、UFSなどの `compatible`、`reg`、割り込みとクロックの接続。親バスの `ranges` で物理アドレスへ換算する。 |
| 同居設定 | 最終DTBのOpenSBIドメイン、開始アドレス、OP-TEE private／共有メモリの権限、MPXYチャネルとhartの対応。 |

各対象について「DT記述が一致」「試験プロファイル由来の差」「QEMUモデルの差」
「未確認」と、起動・試験への影響を記録する。DTの一致とデバイスの動作確認は
別々に記録する。

### 実機DTBを土台にQEMU起動を試す

比較後、実機DTBのコピーでQEMUが提供するCPU、メモリ、割り込み、シリアル、
起動ディスクと整合することを確認する。試験に必要な機器がQEMUで未実装なら、
その機器に依存する試験を未検証と記録する。コピーにOpenSBIドメインを設定し、
[同居DTB生成手順](jupiter2-optee-ftpm-porting-plan.md)に従って予約メモリと
MPXY設定を追加したものを `run-k3.sh --dtb` に渡す。使用したDTBのハッシュと
UARTを保存し、LinuxのCPU列挙、OP-TEE起動、Keystone試験の結果をQEMU由来DTBでの
基準起動と比較する。実機DTB原本とQEMU用に変更したコピーをそれぞれ保持する。

### 2026-11-24のビルドとDTB照合

現行ソースの `riscv64-softmmu` ビルドディレクトリで
`ninja -C .build-k3/qemu qemu-system-riscv64` を実行し、QEMU 11.1.3を差分ビルドした。
このホストではMesonのPythonモジュールのパスを指定し、静的GLibが要求する
`libsysprof-capture-4.a` をリンク時に追加した。空き容量を抑えるためデバッグシンボルを除いた。

`qemu.conf` の16 hart・2 GiB・均一16 PMP枠で `dumpdtb` を実行し、
`hardware/jupiter2/captures/20261108-075700/running.dtb` と照合した。
16 hart、24 MHzのtimebase、RAMの開始アドレス、CLINT・S-mode IMSIC・
S-mode APLIC・UARTのアドレスと領域サイズが一致した。ルートの
`compatible` はQEMUが `riscv-virtio`、実機が `spacemit,k3-pico-itx`。
実機のRPMI共有メモリノードはQEMUの生成DTBにない。
実機相当の32,736 MiBではホストのメモリ確保に失敗した。
今回の検証範囲は差分ビルドとDTB生成・照合で、Linuxゲストは起動していない。
