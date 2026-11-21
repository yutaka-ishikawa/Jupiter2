# Jupiter2 QEMU：起動・guest操作・既存環境の更新

READMEからQEMU固有の運用説明を分離したページです。
実機への配置・RAM起動は[READMEのフェーズ3](../README.md#phase-deploy)、
build/installの仕様は[make手順](make-build-install.md)を参照してください。
以下の開発PCのコマンドはpublicリポジトリのルートで実行します。

## 1. 起動に使う配置先とファイル

| 選択 | 既定の配置先 | guest rootfs |
| --- | --- | --- |
| Keystone（既定） | `install/keystone/` | `rootfs/keystone-rootfs.img` |
| Bianbu | `install/bianbu/` | `rootfs/bianbu-rootfs.img` |

両者は同じK3向けQEMU/OpenSBI/Linuxソースを使用し、Keystone側には対応driver・SDK/Eyrieのsample・guest用ツールを追加します。
QEMU機種は`jupiter2`で、upstream Keystoneの`virt`へ切り替える構成ではありません。
ただしJupiter2モデルは`virt`に基づく部分モデルです。実機との差は[不足一覧](jupiter2-qemu-hardware-test-gaps.md)を参照してください。

通常のMakefileでは、先にbuildを行い、開発PCの実行用ディレクトリへ配置します。

```bash
make build JOBS=20
make install
```

**installで既存rootfsを更新する前に、QEMUを正常shutdownし、ホストでマウント中ならアンマウント・loop切断してください。**
`make install`はコンパイルを行いません。必要な成果物がない場合は、先に対応するbuildを実行します。

## 2. QEMUの起動オプション

```bash
bash scripts/run-k3.sh
bash scripts/run-k3.sh --image keystone
bash scripts/run-k3.sh --image bianbu

# 同じソースで、従来構成とPMP16/32個混在を比較
bash scripts/run-k3.sh --image keystone --pmp-profile uniform16
bash scripts/run-k3.sh --image keystone --pmp-profile mixed
```

`--image`は既定の配置先を選ぶオプションで、再ビルドは行いません。
既定は16 Hart、2 GiB RAM、診断用の`init=/bin/bash`です。
`uniform16`は全Hartで16個・粒度16バイト、`mixed`はHart0〜7が16個・Hart8〜15が32個、全Hartの粒度4 KiBです。
混在profileはPMPの構成を再現するもので、X100/A100のISAや周辺機器全体を再現するものではありません。

別のインストール先、個別ファイルを指定する例です。

```bash
bash scripts/run-k3.sh --prefix "$PWD/install/keystone-v2"

bash scripts/run-k3.sh --image keystone \
  --qemu /path/to/qemu-system-riscv64 \
  --bios /path/to/fw_dynamic.bin \
  --kernel /path/to/Image \
  --rootfs /path/to/keystone-rootfs.img
```

| オプション | 用途 |
| --- | --- |
| `--hostfs DIR` | guestへ共有するホストディレクトリ。既定はリポジトリ |
| `--sstc on` / `--sstc off` | ホストSstcとSM M_TIMERの共存経路を比較 |
| `--gdb` | resetで停止し、127.0.0.1:1234へ接続待ち |
| `--console` | serial/monitor multiplexer。Ctrl-A Cで切替 |
| `--monitor` | 127.0.0.1:4444のmonitorを有効化 |
| `--memory SIZE` | guestメモリー容量 |
| `--append TEXT` | Linux起動引数の上書き |

Sstc対応時はLinuxのSstcを維持し、EnclaveはSMの独立M_TIMERで扱います。
[共存方式](keystone-sstc-coexistence.md)を参照してください。
以前の「Sstcを全体で抑止する」という説明は現在の方式ではありません。

## 3. guestの共有ディレクトリ・モジュール・shutdown

次はQEMUのLinux guest内で実行します。

```bash
mkdir -p /proc /sys
mountpoint -q /proc || mount -t proc proc /proc
mountpoint -q /sys || mount -t sysfs sysfs /sys
mount-hostshare
/usr/bin/run-keystone-hello
/usr/share/keystone/examples/hello-native.ke
```

`mount-hostshare`は9p共有を`/mnt/host`へマウントします。別名を使う場合は引数を指定します。
`init=/bin/bash`では、各bootでproc/sysfsを準備してください。
`run-keystone-hello`は必要なmount、対応driverのロード、helloの実行を行います。
基本のコマンドがない場合に備え、guest toolsには静的RISC-V BusyBoxを含めています。

```bash
shutdown -h now
# または
poweroff
```

shutdown helperは同期・rootfsのread-only再mount後に終了します。
rootfsをread-onlyにできない場合は停止処理を取り消します。
`sbi_hsm_exit: ERR: The hart is in invalid state [0]`で止まる場合は
[system reset修正](keystone-system-reset.md)を確認してください。

モジュール・ネットワークコマンド、depmod、guestツールの詳細は
[guestコマンド](keystone-guest-commands.md)を参照してください。
QEMU用ツールを実機向けbundleへ一括コピーする手順ではありません。

## 4. sampleとverificationを実行する

### 基本sample群

build/installした後、開発PCで実行します。

```bash
python3 samples/run-qemu.py --basic --crypto unavailable --sstc on
```

この実行は実system QEMUのLinuxからsampleを動かし、ログと入力hashを記録します。
`--basic`ではattestation/sealingを使う例を明示的にスキップします。
暗号sampleを含める場合は、対応するQEMU開発鍵profileと公開metadataを使い、
[samples手順](../samples/README.md)と[crypto試験](../verifications/crypto/README.md)に従ってください。

現在の`samples/run-qemu.py`は通常のlauncher設定を使用し、混在PMP用オプションを引き渡しません。
混在構成はguestでの手動sample実行、または以下の専用試験で別途確認します。

### KSB-073の二種sample・混在PMP回帰試験

実Linux、対応driver、RISC-V共有ライブラリー、hello/nativeを含む専用initramfsを使います。
実行コマンド、試験用kernel設定、修正前後のUART、binary hashは
[UTM復帰の比較試験](jupiter2-utm-host-access-issue.md#6-実qemuでのsample回帰試験結果)に記録しています。
スクリプトは`../scripts/tests/jupiter2-ram-boot/`に置いています。

### verification全体

開発PCで必要なguestプログラムと対応kernel modulesをビルドします。

```bash
make verifications JOBS=20
make install-verifications
```

その後、対応する実Linux guest内で[verification手順](../verifications/README.md)のrun-allを実行します。
build、sample二種、専用の起動試験、verification全体の結果は別に記録してください。
[検証方法](keystone-verification-methods.md)に試験範囲の区別を記載しています。

## 5. 既存環境を更新する

### SM/OpenSBIだけを更新する

guestを停止した後、開発PCで実行します。

```bash
make firmware JOBS=20
make install-opensbi
bash scripts/run-k3.sh --image keystone
```

`PREFIX`等を変更している場合はbuild/install/runで同じディレクトリを指定します。
SMだけの変更にkernelやrootfsの置換は不要ですが、更新したfirmwareでsampleを再実行してください。

### SDK/Eyrie/sampleを更新する

開発PCで再ビルドし、停止済みguest用の配置を更新します。

```bash
make keystone JOBS=20
make install-eyrie install-linux install-samples install-keystone
```

`make keystone`で現在のpackageと対応driverを含むguest-overlayも作り直します。
`install-keystone`はそのoverlayをrootfsへ反映します。

起動したguestの共有ディレクトリから、基本packageだけを更新する方法もあります。

```bash
mount-hostshare
cp /mnt/host/.build-keystone/examples/hello/hello.ke /usr/share/keystone/examples/hello.ke
cp /mnt/host/.build-keystone/examples/hello-native/hello-native.ke /usr/share/keystone/examples/hello-native.ke
chmod +x /usr/share/keystone/examples/*.ke
run-keystone-hello
```

`--hostfs`やビルド先を変更した場合はパスを合わせます。

### guest helperだけを更新する

開発PCでhelperをビルドします。

```bash
bash scripts/build-keystone-guest-tools.sh
```

guestで共有を準備し、installerを実行します。

```bash
mkdir -p /mnt/host
mountpoint -q /mnt/host || mount -t 9p -o trans=virtio,version=9p2000.L hostshare /mnt/host
bash /mnt/host/scripts/install-keystone-guest-tools.sh
```

helperの配置だけでは、通常のBianbu imageへKeystone driverやsampleは追加されません。

## 6. Bianbu用・旧一括スクリプトを使う場合

通常はREADMEのmakeによるbuild/install分離を使います。
既存の一括スクリプトを使う場合の入口は次です。

```bash
# Bianbu側のQEMU/kernel/firmware/rootfs
bash scripts/build-install-k3.sh --jobs 20

# Bianbu rootfsだけを作成
bash scripts/build-install-k3.sh --only rootfs

# SDK/Eyrie/sampleだけを準備
bash scripts/build-install-keystone.sh --only sdk --jobs 20
```

`build-install-k3.sh`には`--only qemu|firmware|linux`、`--prefix`、`--build-dir`もあります。
Keystone一括スクリプトは既存BianbuのQEMU/kernelを再利用でき、firmwareは現在のSM/OpenSBIからビルドします。
対応kernel buildのImageとModule.symversが必要です。

```bash
# 既存imageを残し、新しい配置先に作る例
bash scripts/build-install-keystone.sh \
  --base-prefix "$PWD/install/keystone" --prefix "$PWD/install/keystone-v2" --jobs 20
bash scripts/run-k3.sh --prefix "$PWD/install/keystone-v2"
```

rootfsは[Bianbu 26.04 base](https://archive.spacemit.com/bianbu-base/bianbu-base-26.04-base-riscv64.tar.gz)から作る8 GiBのsparse ext4です。
アーカイブを手元に用意する場合は`--rootfs-archive FILE`、独立に取得したhashがある場合は`--rootfs-sha256 HASH`を指定します。
古いmke2fsではfakerootでディレクトリ入力を使い、所有者・mode・link・device nodeを保持します。
このfallbackでは拡張ACL・file capabilityの復元は行いません。
rootfs作成・更新とcompilerの起動は、使用するmakeターゲット・スクリプトの役割を確認して区別してください。

## 7. 停止位置の調査とbuildのcleanup

RCU stallの表示だけでタイマーが原因とは断定できません。
実行中guestを止め、必要な場合だけSMの進捗ログを有効にします。

```bash
KEYSTONE_SM_TRACE=1 make firmware JOBS=20
make install-opensbi
bash scripts/run-k3.sh --image keystone
```

boot時のtrace有効表示を確認し、CREATE、PMP broadcast/ACK、hash、RUN等の最後の完了位置を記録します。
戻す場合は`KEYSTONE_SM_TRACE=0 make firmware`から再build/installします。
PMP検査を解除したり、停止箇所の確認なしにtimeoutだけを増やしたりする手順ではありません。

| 症状・目的 | 詳細 |
| --- | --- |
| Eyrie入口のIllegal instruction、build-id/loaderの問題 | [Eyrie入口調査](keystone-eyrie-entry-build-id.md)、[累積修正記録](keystone-cumulative-changes.md) |
| host dispatchのUTM読み取りで終了139 | [KSB-073](jupiter2-utm-host-access-issue.md) |
| 大容量EPMとCMA | [大容量EPM](keystone-large-epm.md) |
| module/networkコマンド不足 | [guestコマンド](keystone-guest-commands.md) |
| source変更ごとの更新対象 | [make手順](make-build-install.md) |

生成したbuild中間物を掃除する場合は、実行中のbuildを停止してから専用スクリプトを使います。

```bash
bash scripts/clean-k3.sh --dry-run
bash scripts/clean-k3.sh --only firmware
```

`--only qemu|linux`、`--build-dir DIR`も指定できます。
source、保存したrootfs、install済みファイルの削除とは別です。

## 8. 現在の確認範囲

以前のsample実行結果は[samples/results.md](../samples/results.md)、
KSB-073修正前後の実Linuxでの二種8回の結果は[比較試験](jupiter2-utm-host-access-issue.md)を参照してください。
このページの操作例を掲載したこと自体は、全profile・全sample・全verificationを再実行したという意味ではありません。
QEMUと実機の違い、検証済み範囲は[不足一覧](jupiter2-qemu-hardware-test-gaps.md)と[不具合台帳](keystone-bug-report.md)で追跡します。
