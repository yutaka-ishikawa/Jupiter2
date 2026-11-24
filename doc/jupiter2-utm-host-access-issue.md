# Jupiter2：OCALL復帰後のUTM読み取りでhelloが停止する問題（KSB-073）

更新：2026年11月21日。対応する[不具合台帳](keystone-bug-report.md#ksb-073-全16-cpu起動後hello二種のhost-runnerがload-access-faultで停止)。

## 1. 実機で確認した症状

PMP混在対応後の利用者提供dmesgでは、Linuxが全16 CPUを起動している。
一方、hello.keとhello-native.keはいずれもホスト側runnerのSIGSEGVで停止した。
hello-nativeの終了コードは139。両方の例外はcause=5（load access fault）である。
直前にEPM 4 MiBを物理0x11c000000へ割り当てた記録があるが、障害VAをEPMのVAと断定してはいけない。
以下のELF照合により、障害はUTM上のOCALL headerの読み取りと判明した。

## 2. 配布packageと障害命令の照合

利用者が実機に配置した二つのpackageを提供した。
自己展開shellを実行せず、headerのpayload長とMD5を確認してgzip/tarを読み取り、runner ELFを静的解析した。
提供されたRISC-V runnerやEnclaveは開発ホストでは実行していない。

| 入力 | bytes | SHA-256 |
| --- | ---: | --- |
| hello.ke | 503855 | bfb080bbcb7494fffe58af8ae3f5d8671075fb4c3592d186aab02641f5cd752f |
| hello-native.ke | 212331 | 4f63436b50febe468f10f0f789d81f53612c0e8c9dc3b9b6b46cf548f7628879 |
| hello-runner | 303648 | 9a5b566a219cde8654990a3dbb72626b66e39af4594a69369b014df8ae21f8cd |
| hello-native-runner | 303424 | 715cb1b1a3ed143d0e55b641b9e3e7185214d83ceee8a1a5be70f45e62233210 |

| 対象 | ELF内障害位置 | 関数 | 命令 | RAのELF内位置 |
| --- | ---: | --- | --- | ---: |
| hello-runner | 0x529c | dispatch(void*)+8 | ld a4,0(a0)（0x6118） | 0x6092 |
| hello-native-runner | 0x5244 | dispatch(void*)+8 | ld a4,0(a0)（0x6118） | 0x603c |

RAはいずれもKeystone::Enclave::run()内のOCALL callback呼出し直後と一致する。
`Enclave::run()`はEdgeCallHostで `oFuncDispatch(getSharedBuffer())` を呼ぶ。
`samples/common/runner.hpp`のdispatch()は、最初にbufferをedge_callとして扱いcall_idを読む。
実機例外のa0とbadaddrは一致し、この最初の読み取りが失敗している。
CREATEとRUNが進んでOCALL dispatchへ到達した証拠であり、初期ELFロード時の失敗とは異なる。
Enclaveの完走や隔離の成功を意味するものではない。

## 3. ソース上の原因

K3向けのKSB-062修正では、UTMをOS全体のPMP規則と別のエントリーへ割り当てるようにした。
このUTMエントリーはOSの広域許可エントリーより前に置かれる。

一方、`keystone/sm/src/enclave.c`のrevoke_region()は、BACKING以外の全regionにPMP_NO_PERMを設定していた。
UTMもこの処理を受けるため、ホストへ戻った後もUTMを指すアクセス禁止規則が有効なまま残る。
後でOSの広域許可を復帰しても、PMPの先に一致したUTM禁止規則が優先され、ホストが共有bufferを読めない。

| 対象 | Enclave実行中 | 修正前のホスト復帰 | 修正後のホスト復帰 |
| --- | --- | --- | --- |
| EPM | Enclave用の許可 | アクセス禁止 | アクセス禁止を維持 |
| UTM | Enclave用の許可 | 独立規則でアクセス禁止 | 独立規則をOFF、OSの許可規則へ到達 |
| OS全体 | アクセス禁止 | 許可へ復帰 | 許可へ復帰 |

この不整合はK3移植でUTMを独立させた処理と、既存の復帰処理の組合せにある。
上流Keystone一般の不具合とは帰属しない。
実機でのPMP CSR dumpや障害VAのPTEはまだ採取していないが、同一ELFで特定した障害位置とソース上の禁止規則が一致している。
修正版による実機の正常終了を確認するまでは、解決済みとは扱わない。

## 4. 修正内容

修正コミット：[76fd41362565](https://github.com/yutaka-ishikawa/public/commit/76fd41362565e0f53f7216a42fa95ac41df1271e)。

K3構成のREGION_UTMに限り、revoke_region()から既存のk3_pmp_apply_verified()を使い、
ローカルのUTMエントリーをUNSETする。
これにより実CSRの読み戻しと、実装が32個の場合の追加範囲検査も受ける。
読み戻しに失敗した場合は、従来の呼出し元と同じくホストへ復帰せず停止する。

この共通helperは通常のホスト復帰と、Enclaveへの切替失敗時のrollbackの両方で使われる。
EPMのNO_PERM、OS切替、root domainの保護・ロック、UTMの割当て所有権は変更しない。
UTMの共有アクセスを復帰させるもので、PMP全体を解除する変更ではない。
汎用構成のUTM処理と既存BACKING処理は変更しない。

修正対象はSMのみ。今回の原因への対応として、Linux、driver、SDK、hello二種を作り直す必要はない。

## 5. ビルドと実機での再試験

開発PCのpublicリポジトリを最新にした後、同じビルド条件で実行する。
CROSS_COMPILEは以前の参照FSBL/U-Bootビルドに使用したprefixを設定しておく。

```bash
make firmware JOBS=20

python3 scripts/build-jupiter2-reference-ram-boot.py \
  --opensbi-bin .build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin \
  --esos-itb hardware/jupiter2/vendor/esos.itb \
  --esos-configuration conf_dual \
  --variant keystone \
  --opensbi-reserve-bytes 0x00100000 \
  --max-download-bytes 0x20000000 \
  --cross-compile "$CROSS_COMPILE" \
  --output work/jupiter2-ram-boot/reference-keystone-utm-host-fix
```

出力先は未作成のディレクトリを指定する。
生成したrelease/imagesのFSBLと統合FITを対で使い、[RAM起動ガイド](jupiter2-ram-boot-guide.md)の手順で起動する。
NORへの書き込みは行わない。
Linux起動後は[アプリ試験第6章](jupiter2-keystone-app-test.md#6-ドライバーとhello二種を試験する実機linux)に従い、
onlineが0-15であることを確認してから実行する。

```bash
sudo /opt/keystone/6.18.3/hello.ke
echo "hello終了コード=$?"
sudo dmesg | tail -n 100
```

helloが正常終了し、終了コード0でエラーがなければ次へ進む。

```bash
sudo /opt/keystone/6.18.3/hello-native.ke
echo "hello-native終了コード=$?"
sudo dmesg | tail -n 100
```

両方のアプリの期待出力・終了コード0、UTMへのホスト読み取り成功、SM/Linuxの例外なしを確認する。
どちらかが失敗した場合は反復実行せず、その時点のUARTとdmesgを保存する。
修正版のfirmware hashも記録し、今回解析した旧版packageのhashと混同しない。

## 6. 実QEMUでのsample回帰試験結果

### 入力をそろえた比較

試験用Linux 6.18.3-ksb073-qemuと対応する実Keystone driverをビルドし、
利用者提供packageから取り出した同一のrunner・SDK・Eyrie・eappをLinux guestで実行した。
SBI/PMP/CSRのモックや、本体関数を抜き出した試験ではない。
以前の小さなS-mode guestの起動確認から進め、実sampleのOCALL、RESUME、終了、DESTROYまで確認した。

両試験で同じQEMU、kernel、driver、initramfs、sampleを使用する。
SMはK3のUTM復帰処理の修正有無を変えて比較した。
crypto providerはunavailable、Sstcはon、全16 CPU online。
CPU3/8はLinuxの論理CPU番号であり、実機X100/A100のCPU実装全体を再現したという意味ではない。

| SM | PMP構成 | 実行条件 | 結果 |
| --- | --- | --- | --- |
| 修正前 | 全Hart 16個、粒度16バイト | hello、CPU3固定 | runner+0x529cでcause=5、終了139を再現。後続は停止 |
| 修正前 | 前半16個/後半32個、粒度4 KiB | hello、CPU3固定 | 同じ位置・例外・終了139を再現。後続は停止 |
| 修正後 | 全Hart 16個、粒度16バイト | hello/nativeをCPU3/8で各1回 | 4回すべて正常出力・終了0・DESTROY |
| 修正後 | 前半16個/後半32個、粒度4 KiB | hello/nativeをCPU3/8で各1回 | 4回すべて正常出力・終了0・DESTROY |

**修正後の計8回はすべて成功。修正前の期待失敗の再現は2構成で成功した。**
results.jsonのreferenceケースのpass=trueは「終了139を正しく再現できた」という意味であり、
sampleの正常終了を意味しない。

修正後の出力例：

```text
KSB073-SAMPLES: RUN hello cpu=3
hello, world!
PASS SAMPLE hello: enclave exit=0 DESTROY
KSB073-SAMPLES: EXIT hello cpu=3 0
KSB073-SAMPLES: RUN hello-native cpu=3
Hello World
PASS SAMPLE hello-native: enclave exit=0 DESTROY
KSB073-SAMPLES: EXIT hello-native cpu=3 0
...
KSB073-SAMPLES: PASS ALL
```

### なぜ以前のQEMU試験では発覚しなかったか

[samples/results.md](../samples/results.md)には11月9日の版でsample群がPASSした記録がある。
一方、UTMを独立PMPエントリーへ変更したKSB-062は11月21日の変更である。
その変更後に同じ成果物でOCALLまで含むsampleの回帰試験を再実行できていなかった。
今回最初に実行した全Hart起動試験はUTM復帰経路を通らないため、この不備を検出できない。

今回、QEMUでも修正前コードで実機と同じEPC相対位置・cause・終了コードを再現できた。
したがって、この問題はQEMUで原理的に再現できない障害ではなく、
UTM割当て変更に対する回帰確認の不足によって見逃した不具合である。
過去版でのsample PASSを、変更後の成果物のPASSとして扱ってはいけない。

### 証跡と再実行

- [実行manifestと入力binary hash](evidence/jupiter2-ksb073/results.json)
- [source・driver・package hashと試験範囲](evidence/jupiter2-ksb073/build-inputs.json)
- [修正後・一律構成UART](evidence/jupiter2-ksb073/fixed-uniform16.log)
- [修正後・混在構成UART](evidence/jupiter2-ksb073/fixed-mixed.log)
- [修正前・一律構成UART](evidence/jupiter2-ksb073/reference-uniform16.log)
- [修正前・混在構成UART](evidence/jupiter2-ksb073/reference-mixed.log)

専用スクリプトはscripts/tests/jupiter2-ram-bootに置き、目的と実行場所を冒頭に記載した。
linux-sample-init.shはLinux guestの/init用であり、開発PCの通常shellで実行しない。
試験用kernel設定はlinux-sample-kernel.config。実機へ導入するkernelの設定ではない。
initramfsにはBusyBox、実runnerの実行に必要なRISC-V共有ライブラリー、
対応kernelでビルドしたkeystone-driver.ko、二つのpackage内容を置く。
その/initとしてlinux-sample-init.shを配置する。

```bash
# 開発PC。用意した同一kernel/initramfsと比較対象firmwareを指定する。
python3 scripts/tests/jupiter2-ram-boot/run_linux_sample_regression.py \
  --qemu install/keystone/bin/qemu-system-riscv64 \
  --kernel work/ksb073-qemu-linux/kernel/arch/riscv/boot/Image \
  --initrd work/ksb073-qemu-linux/initramfs.cpio.gz \
  --firmware work/ksb073-fixed-sm/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin \
  --reference-firmware work/ksb073-old-sm/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin \
  --output work/ksb073-linux-sample-results
```

修正前firmwareを用意していなければ--reference-firmwareを省略し、修正後の2構成だけを試験できる。
出力先は未作成のディレクトリを指定する。失敗時もUARTログとmanifestを保持する。

比較試験の修正後raw bin SHA-256：
`ee9e120631da81a87b63862593470a44d4431bf808b1d9d942fbb9202d80e279`。
ビルド条件やツールが違えばhashは変わるため、利用者側の成果物も記録する。

### 検証限界

SMの全30 translation unitsのクロスコンパイル、OpenSBIリンク、mtvec整列も確認した。
今回の実guestで確認したsampleはhelloとhello-nativeの二種であり、全12 sampleや
verifications/run-all.sh全体のPASSではない。
EPM保護を変更していないことは差分で確認したが、ホストによるEPM読み取り拒否の負の試験は未実施。
実機での修正版hello二種の再試験も未実施。
QEMUは実機のroot13個・空き3個・ロック、PMPADDR幅38ビット、ESOS/RPMI/UFSを完全には再現していない。
試験用Linuxの小さい設定とDebianの実行ライブラリーを使用しており、Bianbu実機全体の検証とは区別する。
